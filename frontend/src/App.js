import React, { useState, useEffect } from 'react';
import {
  Container,
  Paper,
  Typography,
  TextField,
  Button,
  Box,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Grid,
  Card,
  CardContent,
  InputAdornment,
  CircularProgress,
  Alert,
  Snackbar,
  ListSubheader,
} from '@mui/material';
import axios from 'axios';
import { LoadingButton } from '@mui/lab';
import AddIcon from '@mui/icons-material/Add';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const MBTI_TYPES = [
  'UNKNOWN',
  'INTJ', 'INTP', 'ENTJ', 'ENTP',
  'INFJ', 'INFP', 'ENFJ', 'ENFP',
  'ISTJ', 'ISFJ', 'ESTJ', 'ESFJ',
  'ISTP', 'ISFP', 'ESTP', 'ESFP'
];

const MONTHS = Array.from({ length: 12 }, (_, i) => ({
  value: i + 1,
  label: `${i + 1}月`
}));

const MIN_BUDGET = 30000;
const MAX_BUDGET = 500000;
const BUDGET_STEP = 10000;

// 都道府県データ
const PREFECTURES = [
  { id: 'hokkaido', name: '北海道', region: '北海道' },
  { id: 'aomori', name: '青森県', region: '東北' },
  { id: 'iwate', name: '岩手県', region: '東北' },
  { id: 'miyagi', name: '宮城県', region: '東北' },
  { id: 'akita', name: '秋田県', region: '東北' },
  { id: 'yamagata', name: '山形県', region: '東北' },
  { id: 'fukushima', name: '福島県', region: '東北' },
  { id: 'ibaraki', name: '茨城県', region: '関東' },
  { id: 'tochigi', name: '栃木県', region: '関東' },
  { id: 'gunma', name: '群馬県', region: '関東' },
  { id: 'saitama', name: '埼玉県', region: '関東' },
  { id: 'chiba', name: '千葉県', region: '関東' },
  { id: 'tokyo', name: '東京都', region: '関東' },
  { id: 'kanagawa', name: '神奈川県', region: '関東' },
  { id: 'niigata', name: '新潟県', region: '中部' },
  { id: 'toyama', name: '富山県', region: '中部' },
  { id: 'ishikawa', name: '石川県', region: '中部' },
  { id: 'fukui', name: '福井県', region: '中部' },
  { id: 'yamanashi', name: '山梨県', region: '中部' },
  { id: 'nagano', name: '長野県', region: '中部' },
  { id: 'gifu', name: '岐阜県', region: '中部' },
  { id: 'shizuoka', name: '静岡県', region: '中部' },
  { id: 'aichi', name: '愛知県', region: '中部' },
  { id: 'mie', name: '三重県', region: '関西' },
  { id: 'shiga', name: '滋賀県', region: '関西' },
  { id: 'kyoto', name: '京都府', region: '関西' },
  { id: 'osaka', name: '大阪府', region: '関西' },
  { id: 'hyogo', name: '兵庫県', region: '関西' },
  { id: 'nara', name: '奈良県', region: '関西' },
  { id: 'wakayama', name: '和歌山県', region: '関西' },
  { id: 'tottori', name: '鳥取県', region: '中国' },
  { id: 'shimane', name: '島根県', region: '中国' },
  { id: 'okayama', name: '岡山県', region: '中国' },
  { id: 'hiroshima', name: '広島県', region: '中国' },
  { id: 'yamaguchi', name: '山口県', region: '中国' },
  { id: 'tokushima', name: '徳島県', region: '四国' },
  { id: 'kagawa', name: '香川県', region: '四国' },
  { id: 'ehime', name: '愛媛県', region: '四国' },
  { id: 'kochi', name: '高知県', region: '四国' },
  { id: 'fukuoka', name: '福岡県', region: '九州' },
  { id: 'saga', name: '佐賀県', region: '九州' },
  { id: 'nagasaki', name: '長崎県', region: '九州' },
  { id: 'kumamoto', name: '熊本県', region: '九州' },
  { id: 'oita', name: '大分県', region: '九州' },
  { id: 'miyazaki', name: '宮崎県', region: '九州' },
  { id: 'kagoshima', name: '鹿児島県', region: '九州' },
  { id: 'okinawa', name: '沖縄県', region: '沖縄' }
];

// 地方ごとにグループ化された都道府県を取得
const groupedPrefectures = PREFECTURES.reduce((acc, pref) => {
  if (!acc[pref.region]) {
    acc[pref.region] = [];
  }
  acc[pref.region].push(pref);
  return acc;
}, {});

// 写真URLを処理するカスタムコンポーネント
const HotelImage = ({ src, alt }) => {
  const [imageUrl, setImageUrl] = useState('');
  const [error, setError] = useState(false);
  const apiKey = process.env.REACT_APP_GOOGLE_MAPS_API_KEY;

  useEffect(() => {
    if (src && apiKey) {
      const newUrl = src.includes('?') ? `${src}&key=${apiKey}` : `${src}?key=${apiKey}`;
      setImageUrl(newUrl);
      console.log('Image URL generated:', newUrl);
    }
  }, [src, apiKey]);

  if (error) return null;

  return (
    <img
      src={imageUrl}
      alt={alt || '施設写真'}
      style={{
        height: '200px',
        marginRight: '10px',
        marginBottom: '10px',
        objectFit: 'cover',
        borderRadius: '8px',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}
      onError={(e) => {
        console.error('Image load error:', e);
        setError(true);
      }}
      onLoad={() => {
        console.log('Image loaded successfully:', imageUrl);
      }}
    />
  );
};

// 宿泊グレードの定義を追加
const ACCOMMODATION_GRADES = [
  { value: 'エコノミー', label: 'エコノミー（〜15,000円）', price_range: 15000 },
  { value: 'スタンダード', label: 'スタンダード（15,000円〜30,000円）', price_range: 30000 },
  { value: 'ラグジュアリー', label: 'ラグジュアリー（30,000円〜50,000円）', price_range: 50000 },
  { value: 'ウルトララグジュアリー', label: 'ウルトララグジュアリー（50,000円〜）', price_range: 100000 }
];

function App() {
  const [members, setMembers] = useState([{
    age: 25,
    gender: 'male',
    mbti: 'INTJ'
  }, {
    age: 28,
    gender: 'female',
    mbti: 'ENFP'
  }]);
  const [departureLocation, setDepartureLocation] = useState('東京');
  const [departurePrefecture, setDeparturePrefecture] = useState('tokyo');
  const [travelMonth, setTravelMonth] = useState(3);
  const [nights, setNights] = useState(1);
  const [accommodationGrade, setAccommodationGrade] = useState('スタンダード');
  const [travelPlan, setTravelPlan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [generatingStatus, setGeneratingStatus] = useState('');
  const [error, setError] = useState(null);
  const [snackbarOpen, setSnackbarOpen] = useState(false);

  const addMember = () => {
    setMembers([...members, { age: 25, gender: 'male', mbti: 'UNKNOWN' }]);
  };

  const updateMember = (index, field, value) => {
    const newMembers = [...members];
    newMembers[index] = { ...newMembers[index], [field]: value };
    setMembers(newMembers);
  };

  const removeMember = (indexToRemove) => {
    if (members.length > 1) {
      setMembers(members.filter((_, index) => index !== indexToRemove));
    } else {
      displayError('メンバーは最低1人必要です');
    }
  };

  const handleCloseSnackbar = () => {
    setSnackbarOpen(false);
  };

  const displayError = (errorMessage, errorDetails = null) => {
    let message = errorMessage;
    if (errorDetails) {
      if (errorDetails.validation_errors) {
        message = Object.entries(errorDetails.validation_errors)
          .map(([field, msg]) => `${field}: ${msg}`)
          .join('\n');
      } else if (errorDetails.error) {
        message = errorDetails.error;
      }
    }
    setError(message);
    setSnackbarOpen(true);
  };

  const handleSubmit = async () => {
    try {
      if (!validateForm()) {
        return;
      }

      setLoading(true);
      setGeneratingStatus('旅行プランを生成中...');
      setError(null);
      
      // メンバーデータの整形
      const formattedMembers = members.map(member => ({
        age: parseInt(member.age),
        gender: member.gender,
        mbti: member.mbti || 'UNKNOWN'
      }));

      const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';
      const requestData = {
        members: formattedMembers,
        departure_location: departureLocation.trim(),
        departure_region: PREFECTURES.find(p => p.id === departurePrefecture)?.region || '',
        travel_month: parseInt(travelMonth),
        nights: parseInt(nights),
        accommodation_grade: accommodationGrade
      };

      console.log('Sending request:', requestData);  // デバッグ用

      const response = await axios.post(`${apiUrl}/api/travel-plan`, requestData);
      
      setTravelPlan(response.data);
      setGeneratingStatus('');
      
    } catch (error) {
      console.error('Error:', error);
      setGeneratingStatus('');
      
      if (error.response) {
        const { data } = error.response;
        console.log('Error response:', data);  // デバッグ用
        displayError(data.message, data.details);
      } else if (error.request) {
        displayError('サーバーに接続できません。インターネット接続を確認してください。');
      } else {
        displayError('予期せぬエラーが発生しました。');
      }
    } finally {
      setLoading(false);
    }
  };

  const validateForm = () => {
    if (!departureLocation.trim()) {
      displayError('出発地を入力してください');
      return false;
    }
    
    if (members.length === 0) {
      displayError('少なくとも1人のメンバーを指定してください');
      return false;
    }
    
    for (const member of members) {
      if (!member.age || member.age < 0 || member.age > 120) {
        displayError('年齢は0-120の範囲で指定してください');
        return false;
      }
    }
    
    return true;
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        旅行プランナー
      </Typography>

      <Paper elevation={3} sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom>
          旅行メンバー情報
        </Typography>
        
        {members.map((member, index) => (
          <Box key={index} sx={{ mb: 3 }}>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={3}>
                <TextField
                  fullWidth
                  label="年齢"
                  type="number"
                  value={member.age}
                  onChange={(e) => updateMember(index, 'age', e.target.value)}
                  InputProps={{
                    inputProps: { min: 0, max: 120 }
                  }}
                />
              </Grid>
              <Grid item xs={3}>
                <FormControl fullWidth>
                  <InputLabel>性別</InputLabel>
                  <Select
                    value={member.gender}
                    label="性別"
                    onChange={(e) => updateMember(index, 'gender', e.target.value)}
                  >
                    <MenuItem value="male">男性</MenuItem>
                    <MenuItem value="female">女性</MenuItem>
                    <MenuItem value="other">その他</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={3}>
                <FormControl fullWidth>
                  <InputLabel>MBTI</InputLabel>
                  <Select
                    value={member.mbti}
                    label="MBTI"
                    onChange={(e) => updateMember(index, 'mbti', e.target.value)}
                  >
                    {MBTI_TYPES.map((type) => (
                      <MenuItem key={type} value={type}>
                        {type === 'UNKNOWN' ? '不明' : type}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={3}>
                <Button
                  variant="outlined"
                  color="error"
                  onClick={() => removeMember(index)}
                  disabled={members.length === 1}
                  fullWidth
                >
                  削除
                </Button>
              </Grid>
            </Grid>
          </Box>
        ))}

        <Button 
          variant="outlined" 
          onClick={addMember} 
          sx={{ mb: 3 }}
          startIcon={<AddIcon />}
        >
          メンバーを追加
        </Button>

        <Grid container spacing={2}>
          <Grid item xs={12}>
            <FormControl fullWidth>
              <InputLabel>出発地</InputLabel>
              <Select
                value={departurePrefecture}
                label="出発地"
                onChange={(e) => {
                  const selected = PREFECTURES.find(p => p.id === e.target.value);
                  setDeparturePrefecture(e.target.value);
                  setDepartureLocation(selected.name);
                }}
              >
                {Object.entries(groupedPrefectures).map(([region, prefectures]) => [
                  <ListSubheader key={region}>{region}</ListSubheader>,
                  ...prefectures.map(pref => (
                    <MenuItem key={pref.id} value={pref.id}>
                      {pref.name}
                    </MenuItem>
                  ))
                ])}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={4}>
            <FormControl fullWidth>
              <InputLabel>旅行月</InputLabel>
              <Select
                value={travelMonth}
                label="旅行月"
                onChange={(e) => setTravelMonth(e.target.value)}
              >
                {MONTHS.map((month) => (
                  <MenuItem key={month.value} value={month.value}>
                    {month.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={4}>
            <FormControl fullWidth>
              <InputLabel>宿泊数</InputLabel>
              <Select
                value={nights}
                label="宿泊数"
                onChange={(e) => setNights(e.target.value)}
              >
                <MenuItem value={0}>日帰り</MenuItem>
                <MenuItem value={1}>1泊2日</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={4}>
            <FormControl fullWidth>
              <InputLabel>宿泊グレード</InputLabel>
              <Select
                value={accommodationGrade}
                label="宿泊グレード"
                onChange={(e) => setAccommodationGrade(e.target.value)}
              >
                {ACCOMMODATION_GRADES.map((grade) => (
                  <MenuItem key={grade.value} value={grade.value}>
                    {grade.label}
                  </MenuItem>
                ))}
              </Select>
              <Typography variant="caption" color="textSecondary" sx={{ mt: 1 }}>
                {ACCOMMODATION_GRADES.find(g => g.value === accommodationGrade)?.label}
              </Typography>
            </FormControl>
          </Grid>
        </Grid>

        <LoadingButton
          loading={loading}
          variant="contained"
          color="primary"
          onClick={() => {
            if (validateForm()) {
              handleSubmit();
            }
          }}
          sx={{ mt: 3 }}
          fullWidth
        >
          {loading ? '生成中...' : 'プランを生成'}
        </LoadingButton>

        <Snackbar
          open={snackbarOpen}
          autoHideDuration={6000}
          onClose={handleCloseSnackbar}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        >
          <Alert
            onClose={handleCloseSnackbar}
            severity="error"
            variant="filled"
            sx={{ width: '100%' }}
          >
            {error}
          </Alert>
        </Snackbar>

        {generatingStatus && (
          <Box sx={{ mt: 2, textAlign: 'center' }}>
            <CircularProgress size={24} sx={{ mr: 1 }} />
            <Typography variant="body1" component="span" color="primary">
              {generatingStatus}
            </Typography>
          </Box>
        )}
      </Paper>

      {travelPlan && (
        <Paper elevation={3} sx={{ p: 3, mt: 3 }}>
          <Typography variant="h6" gutterBottom>
            旅行プラン
          </Typography>
          
          <Card>
            <CardContent>
              <Box
                className="markdown-body"
                sx={{
                  '& .markdown-body': {
                    backgroundColor: 'transparent',
                    fontFamily: 'inherit',
                  },
                  '& h1': {
                    fontSize: '2rem',
                    fontWeight: 'bold',
                    borderBottom: '2px solid #1976d2',
                    paddingBottom: '0.5rem',
                    marginTop: '2rem',
                    marginBottom: '1rem',
                    color: '#1976d2'
                  },
                  '& h2': {
                    fontSize: '1.5rem',
                    fontWeight: 'bold',
                    borderBottom: '1px solid #2196f3',
                    paddingBottom: '0.3rem',
                    marginTop: '1.5rem',
                    marginBottom: '1rem',
                    color: '#2196f3'
                  },
                  '& h3': {
                    fontSize: '1.2rem',
                    fontWeight: 'bold',
                    marginTop: '1.2rem',
                    marginBottom: '0.8rem',
                    color: '#1976d2'
                  },
                  '& ul, & ol': {
                    marginLeft: '1.5rem',
                    marginBottom: '1rem',
                    paddingLeft: '1rem'
                  },
                  '& li': {
                    marginBottom: '0.5rem'
                  },
                  '& p': {
                    marginBottom: '1rem',
                    lineHeight: '1.6'
                  },
                  '& hr': {
                    margin: '1rem 0',
                    border: 'none',
                    borderTop: '1px solid #e0e0e0'
                  }
                }}
              >
                {travelPlan && travelPlan.travel_plan && (
                  <ReactMarkdown 
                    children={travelPlan.travel_plan}
                    remarkPlugins={[remarkGfm]}
                    components={{
                      p: ({node, ...props}) => {
                        if (node.children?.some(child => child.type === 'image')) {
                          return (
                            <div style={{ 
                              display: 'flex', 
                              flexWrap: 'wrap', 
                              gap: '10px',
                              marginBottom: '20px',
                              justifyContent: 'center'
                            }}>
                              {props.children}
                            </div>
                          );
                        }
                        return <p {...props} />;
                      },
                      img: ({src, alt = '施設写真', ...props}) => {
                        const apiKey = process.env.REACT_APP_GOOGLE_MAPS_API_KEY;
                        const imageUrl = src && apiKey ? 
                          (src.includes('?') ? `${src}&key=${apiKey}` : `${src}?key=${apiKey}`) : 
                          src;
                        
                        console.log('Processing image URL:', src);
                        console.log('API Key available:', !!apiKey);
                        console.log('Final image URL:', imageUrl);
                        
                        return (
                          <img
                            src={imageUrl}
                            alt={alt}
                            style={{
                              height: '200px',
                              marginRight: '10px',
                              marginBottom: '10px',
                              objectFit: 'cover',
                              borderRadius: '8px',
                              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
                            }}
                            onError={(e) => {
                              console.error('Image load error:', e);
                              console.error('Failed URL:', imageUrl);
                              e.target.style.display = 'none';
                            }}
                            {...props}
                          />
                        );
                      },
                      a: ({href, children}) => (
                        <a href={href} target="_blank" rel="noopener noreferrer">
                          {children}
                        </a>
                      )
                    }}
                  />
                )}
              </Box>
            </CardContent>
          </Card>
        </Paper>
      )}
    </Container>
  );
}

export default App; 